import React from 'react';
import './CandidateGradeCircle.css';

/**
 * Get grade and color from numeric score
 * Matches backend grading thresholds
 */
export const getGrade = (score) => {
  if (score === null || score === undefined) return { grade: 'N/A', color: '#9ca3af' };
  if (score >= 95) return { grade: 'A+', color: '#2D7A52' };
  if (score >= 90) return { grade: 'A', color: '#2D7A52' };
  if (score >= 85) return { grade: 'A-', color: '#22c55e' };
  if (score >= 80) return { grade: 'B+', color: '#84cc16' };
  if (score >= 75) return { grade: 'B', color: '#84cc16' };
  if (score >= 70) return { grade: 'B-', color: '#eab308' };
  if (score >= 65) return { grade: 'C+', color: '#f59e0b' };
  if (score >= 60) return { grade: 'C', color: '#f59e0b' };
  if (score >= 55) return { grade: 'C-', color: '#f97316' };
  if (score >= 50) return { grade: 'D', color: '#ef4444' };
  return { grade: 'F', color: '#dc2626' };
};

/**
 * Get grade description for tooltips
 */
export const getGradeDescription = (grade) => {
  const descriptions = {
    'A+': 'Exceptional - Top candidate',
    'A': 'Excellent - Strong hire',
    'A-': 'Very Good - Recommend hire',
    'B+': 'Good - Consider hire',
    'B': 'Above Average',
    'B-': 'Average - Some concerns',
    'C+': 'Below Average',
    'C': 'Weak - Major concerns',
    'C-': 'Poor - Not recommended',
    'D': 'Very Poor - Do not hire',
    'F': 'Failing - Immediate reject',
    'N/A': 'Not yet assessed'
  };
  return descriptions[grade] || '';
};

/**
 * Circular grade display component
 * Shows letter grade with numeric score
 */
function CandidateGradeCircle({
  score,
  grade: propGrade,
  label,
  size = 'md',
  showScore = true,
  onClick,
  className = ''
}) {
  // Use provided grade or calculate from score
  const { grade, color } = propGrade
    ? { grade: propGrade, color: getGrade(score).color }
    : getGrade(score);

  const sizeClasses = {
    sm: 'grade-circle-sm',
    md: 'grade-circle-md',
    lg: 'grade-circle-lg',
    xl: 'grade-circle-xl'
  };

  return (
    <div
      className={`candidate-grade-wrapper ${className}`}
      onClick={onClick}
      style={{ cursor: onClick ? 'pointer' : 'default' }}
      title={getGradeDescription(grade)}
    >
      <div
        className={`candidate-grade-circle ${sizeClasses[size]}`}
        style={{ borderColor: color }}
      >
        <span
          className="candidate-grade-letter"
          style={{ color }}
        >
          {grade}
        </span>
        {showScore && score !== null && score !== undefined && (
          <span className="candidate-grade-score">
            {typeof score === 'number' ? score.toFixed(1) : score}
          </span>
        )}
      </div>
      {label && (
        <span className="candidate-grade-label">{label}</span>
      )}
    </div>
  );
}

/**
 * Horizontal grade bar showing score distribution
 */
export function GradeBar({ score, showLabel = true, height = 8 }) {
  const { grade, color } = getGrade(score);
  const percentage = Math.min(100, Math.max(0, score || 0));

  return (
    <div className="grade-bar-wrapper">
      <div
        className="grade-bar-track"
        style={{ height: `${height}px` }}
      >
        <div
          className="grade-bar-fill"
          style={{
            width: `${percentage}%`,
            backgroundColor: color
          }}
        />
      </div>
      {showLabel && (
        <div className="grade-bar-labels">
          <span className="grade-bar-score">{score?.toFixed(1) || 0}</span>
          <span className="grade-bar-grade" style={{ color }}>{grade}</span>
        </div>
      )}
    </div>
  );
}

/**
 * Mini grade badge for inline display
 */
export function GradeBadge({ score, grade: propGrade, size = 'sm' }) {
  const { grade, color } = propGrade
    ? { grade: propGrade, color: getGrade(score).color }
    : getGrade(score);

  return (
    <span
      className={`grade-badge grade-badge-${size}`}
      style={{
        backgroundColor: `${color}15`,
        color: color,
        borderColor: color
      }}
    >
      {grade}
    </span>
  );
}

/**
 * Grade legend showing all grades and thresholds
 */
export function GradeLegend({ compact = false }) {
  const grades = [
    { grade: 'A+', min: 95, color: '#2D7A52' },
    { grade: 'A', min: 90, color: '#2D7A52' },
    { grade: 'A-', min: 85, color: '#22c55e' },
    { grade: 'B+', min: 80, color: '#84cc16' },
    { grade: 'B', min: 75, color: '#84cc16' },
    { grade: 'B-', min: 70, color: '#eab308' },
    { grade: 'C+', min: 65, color: '#f59e0b' },
    { grade: 'C', min: 60, color: '#f59e0b' },
    { grade: 'C-', min: 55, color: '#f97316' },
    { grade: 'D', min: 50, color: '#ef4444' },
    { grade: 'F', min: 0, color: '#dc2626' },
  ];

  if (compact) {
    return (
      <div className="grade-legend-compact">
        {grades.filter(g => !g.grade.includes('-') && !g.grade.includes('+')).map(g => (
          <span
            key={g.grade}
            className="grade-legend-item"
            style={{ color: g.color }}
          >
            {g.grade}
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="grade-legend">
      <h4 className="grade-legend-title">Grade Scale</h4>
      <div className="grade-legend-grid">
        {grades.map(g => (
          <div key={g.grade} className="grade-legend-row">
            <span
              className="grade-legend-grade"
              style={{ color: g.color }}
            >
              {g.grade}
            </span>
            <span className="grade-legend-range">
              {g.min}+
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default CandidateGradeCircle;
