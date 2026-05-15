import React from 'react';
import './MotivatorsBarchart.css';

/**
 * Motivator dimension info
 */
const MOTIVATOR_INFO = {
  aesthetic: {
    label: 'Aesthetic',
    color: '#B8924A',
    description: 'Beauty, balance, harmony'
  },
  economic: {
    label: 'Economic',
    color: '#2D7A52',
    description: 'ROI, practicality, results'
  },
  individualistic: {
    label: 'Individualistic',
    color: '#F59E0B',
    description: 'Independence, uniqueness'
  },
  political: {
    label: 'Political',
    color: '#EF4444',
    description: 'Control, influence, power'
  },
  altruistic: {
    label: 'Altruistic',
    color: '#EC4899',
    description: 'Service, helping others'
  },
  regulatory: {
    label: 'Regulatory',
    color: '#B8924A',
    description: 'Order, structure, tradition'
  },
  theoretical: {
    label: 'Theoretical',
    color: '#3B82F6',
    description: 'Knowledge, learning, truth'
  }
};

const DIMENSION_ORDER = [
  'aesthetic',
  'economic',
  'individualistic',
  'political',
  'altruistic',
  'regulatory',
  'theoretical'
];

/**
 * MotivatorsBarchart Component
 * Horizontal bar chart showing 7 motivator dimensions
 */
function MotivatorsBarchart({
  scores = {},
  ranking = {},
  topMotivator = '',
  showRanking = true,
  showDescriptions = false,
  compact = false
}) {
  // Sort dimensions by score descending for display
  const sortedDimensions = [...DIMENSION_ORDER].sort((a, b) => {
    return (scores[b] || 0) - (scores[a] || 0);
  });

  const displayOrder = showRanking ? sortedDimensions : DIMENSION_ORDER;

  return (
    <div className={`motivators-chart ${compact ? 'compact' : ''}`}>
      <div className="motivators-chart-header">
        <h3 className="motivators-chart-title">Motivators Profile</h3>
        {topMotivator && (
          <span
            className="motivators-top-badge"
            style={{ backgroundColor: MOTIVATOR_INFO[topMotivator]?.color }}
          >
            Top: {MOTIVATOR_INFO[topMotivator]?.label}
          </span>
        )}
      </div>

      <div className="motivators-bars">
        {displayOrder.map((dim, index) => {
          const info = MOTIVATOR_INFO[dim];
          const score = scores[dim] || 0;
          const rank = ranking[dim] || index + 1;
          const isTop = rank <= 2;
          const isBottom = rank >= 6;

          return (
            <div
              key={dim}
              className={`motivators-bar-row ${isTop ? 'top' : ''} ${isBottom ? 'bottom' : ''}`}
            >
              <div className="motivators-bar-label">
                {showRanking && (
                  <span
                    className="motivators-rank"
                    style={{
                      backgroundColor: isTop ? info.color : isBottom ? '#e5e7eb' : '#f3f4f6',
                      color: isTop ? '#fff' : '#6b7280'
                    }}
                  >
                    {rank}
                  </span>
                )}
                <span
                  className="motivators-name"
                  style={{ color: info.color }}
                >
                  {info.label}
                </span>
              </div>

              <div className="motivators-bar-track">
                <div
                  className="motivators-bar-fill"
                  style={{
                    width: `${score}%`,
                    backgroundColor: info.color,
                    opacity: isBottom ? 0.5 : 1
                  }}
                />
                <span className="motivators-bar-value">{score}%</span>
              </div>

              {showDescriptions && (
                <span className="motivators-description">{info.description}</span>
              )}
            </div>
          );
        })}
      </div>

      {!compact && (
        <div className="motivators-legend">
          <div className="motivators-legend-item">
            <span className="motivators-legend-dot top" />
            <span>Top Motivators (1-2)</span>
          </div>
          <div className="motivators-legend-item">
            <span className="motivators-legend-dot bottom" />
            <span>Lower Priority (6-7)</span>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Compact motivators display (top 3 only)
 */
export function MotivatorsCompact({ scores = {}, topMotivator = '', secondMotivator = '' }) {
  const topDims = [topMotivator, secondMotivator].filter(Boolean);

  return (
    <div className="motivators-compact">
      {topDims.map((dim, i) => {
        const info = MOTIVATOR_INFO[dim];
        if (!info) return null;

        return (
          <span
            key={dim}
            className="motivators-compact-badge"
            style={{
              backgroundColor: `${info.color}20`,
              color: info.color,
              borderColor: info.color
            }}
          >
            {i === 0 ? '1.' : '2.'} {info.label}
          </span>
        );
      })}
    </div>
  );
}

/**
 * Single motivator bar (for inline display)
 */
export function MotivatorBar({ dimension, score }) {
  const info = MOTIVATOR_INFO[dimension];
  if (!info) return null;

  return (
    <div className="motivator-single-bar">
      <span className="motivator-single-label" style={{ color: info.color }}>
        {info.label}
      </span>
      <div className="motivator-single-track">
        <div
          className="motivator-single-fill"
          style={{ width: `${score}%`, backgroundColor: info.color }}
        />
      </div>
      <span className="motivator-single-value">{score}%</span>
    </div>
  );
}

export default MotivatorsBarchart;
