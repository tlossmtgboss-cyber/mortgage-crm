import React from 'react';
import './DISCProfileChart.css';

/**
 * DISC Style descriptions and colors
 */
const DISC_STYLES = {
  D: {
    label: 'Dominance',
    shortLabel: 'D',
    color: '#ef4444',
    description: 'Results-oriented, competitive, decisive',
    traits: ['Direct', 'Decisive', 'Driven', 'Demanding'],
    loRelevance: 'Drive to close deals and overcome objections'
  },
  I: {
    label: 'Influence',
    shortLabel: 'I',
    color: '#f59e0b',
    description: 'Enthusiastic, optimistic, collaborative',
    traits: ['Inspiring', 'Interactive', 'Impressive', 'Influencing'],
    loRelevance: 'Building rapport and relationships with clients'
  },
  S: {
    label: 'Steadiness',
    shortLabel: 'S',
    color: '#2D7A52',
    description: 'Patient, reliable, team-oriented',
    traits: ['Supportive', 'Stable', 'Sincere', 'Steady'],
    loRelevance: 'Following through on process and client care'
  },
  C: {
    label: 'Conscientiousness',
    shortLabel: 'C',
    color: '#3b82f6',
    description: 'Analytical, precise, systematic',
    traits: ['Careful', 'Cautious', 'Conscientious', 'Calculating'],
    loRelevance: 'Attention to detail and compliance requirements'
  }
};

/**
 * Ideal LO profile for comparison
 * Based on LO-weighted scoring: I=40%, D=30%, S=15%, C=15%
 */
const IDEAL_LO_PROFILE = {
  D: 70,
  I: 85,
  S: 60,
  C: 55
};

/**
 * DISC Profile Chart Component
 * Visual representation of DISC personality assessment
 */
function DISCProfileChart({
  scores = {},
  primaryStyle,
  secondaryStyle,
  showIdealComparison = true,
  showStyleDescriptions = true,
  compact = false,
  editable = false,
  onScoreChange
}) {
  const { D = 0, I = 0, S = 0, C = 0 } = scores;

  // Calculate composite score (LO-weighted)
  const compositeScore = (I * 0.40) + (D * 0.30) + (S * 0.15) + (C * 0.15);

  // Determine primary/secondary if not provided
  const sortedStyles = Object.entries({ D, I, S, C })
    .sort((a, b) => b[1] - a[1]);
  const calculatedPrimary = primaryStyle || sortedStyles[0][0];
  const calculatedSecondary = secondaryStyle || sortedStyles[1][0];

  const handleScoreChange = (style, value) => {
    if (onScoreChange) {
      onScoreChange(style.toLowerCase(), Math.max(0, Math.min(100, parseInt(value) || 0)));
    }
  };

  if (compact) {
    return (
      <div className="disc-chart-compact">
        <div className="disc-compact-bars">
          {['D', 'I', 'S', 'C'].map(style => (
            <div key={style} className="disc-compact-bar">
              <span
                className="disc-compact-label"
                style={{ color: DISC_STYLES[style].color }}
              >
                {style}
              </span>
              <div className="disc-compact-track">
                <div
                  className="disc-compact-fill"
                  style={{
                    width: `${scores[style] || 0}%`,
                    backgroundColor: DISC_STYLES[style].color
                  }}
                />
              </div>
              <span className="disc-compact-value">{scores[style] || 0}</span>
            </div>
          ))}
        </div>
        <div className="disc-compact-styles">
          <span className="disc-style-badge primary" style={{ backgroundColor: DISC_STYLES[calculatedPrimary].color }}>
            {calculatedPrimary}
          </span>
          <span className="disc-style-badge secondary" style={{ borderColor: DISC_STYLES[calculatedSecondary].color, color: DISC_STYLES[calculatedSecondary].color }}>
            {calculatedSecondary}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="disc-chart">
      {/* Header with primary/secondary styles */}
      <div className="disc-chart-header">
        <div className="disc-primary-style">
          <span
            className="disc-style-badge primary large"
            style={{ backgroundColor: DISC_STYLES[calculatedPrimary].color }}
          >
            {calculatedPrimary}
          </span>
          <div className="disc-style-info">
            <span className="disc-style-name">{DISC_STYLES[calculatedPrimary].label}</span>
            <span className="disc-style-type">Primary Style</span>
          </div>
        </div>
        <div className="disc-secondary-style">
          <span
            className="disc-style-badge secondary large"
            style={{ borderColor: DISC_STYLES[calculatedSecondary].color, color: DISC_STYLES[calculatedSecondary].color }}
          >
            {calculatedSecondary}
          </span>
          <div className="disc-style-info">
            <span className="disc-style-name">{DISC_STYLES[calculatedSecondary].label}</span>
            <span className="disc-style-type">Secondary Style</span>
          </div>
        </div>
      </div>

      {/* Composite Score */}
      <div className="disc-composite">
        <span className="disc-composite-label">LO Fit Score</span>
        <span className="disc-composite-value">{compositeScore.toFixed(1)}</span>
      </div>

      {/* Bar Chart */}
      <div className="disc-bars">
        {['D', 'I', 'S', 'C'].map(style => {
          const styleInfo = DISC_STYLES[style];
          const value = scores[style] || 0;
          const idealValue = IDEAL_LO_PROFILE[style];

          return (
            <div key={style} className="disc-bar-row">
              <div className="disc-bar-header">
                <span
                  className="disc-bar-letter"
                  style={{ color: styleInfo.color }}
                >
                  {style}
                </span>
                <span className="disc-bar-label">{styleInfo.label}</span>
                <div className="disc-bar-value-container">
                  {editable ? (
                    <input
                      type="number"
                      className="disc-bar-input"
                      value={value}
                      onChange={(e) => handleScoreChange(style, e.target.value)}
                      min="0"
                      max="100"
                    />
                  ) : (
                    <span className="disc-bar-value">{value}</span>
                  )}
                </div>
              </div>
              <div className="disc-bar-track">
                <div
                  className="disc-bar-fill"
                  style={{
                    width: `${value}%`,
                    backgroundColor: styleInfo.color
                  }}
                />
                {showIdealComparison && (
                  <div
                    className="disc-bar-ideal"
                    style={{ left: `${idealValue}%` }}
                    title={`Ideal LO: ${idealValue}`}
                  />
                )}
              </div>
              {showStyleDescriptions && (
                <p className="disc-bar-description">{styleInfo.loRelevance}</p>
              )}
            </div>
          );
        })}
      </div>

      {/* Legend for ideal comparison */}
      {showIdealComparison && (
        <div className="disc-legend">
          <div className="disc-legend-item">
            <span className="disc-legend-bar actual" />
            <span>Candidate Score</span>
          </div>
          <div className="disc-legend-item">
            <span className="disc-legend-marker ideal" />
            <span>Ideal LO Profile</span>
          </div>
        </div>
      )}

      {/* LO Weight Explanation */}
      <div className="disc-weights-info">
        <h4>LO Role Weighting</h4>
        <p>Influence (40%) + Dominance (30%) + Steadiness (15%) + Conscientiousness (15%)</p>
      </div>
    </div>
  );
}

/**
 * DISC Radar/Spider Chart (alternative visualization)
 */
export function DISCRadarChart({ scores = {}, showIdeal = true, size = 200 }) {
  const { D = 0, I = 0, S = 0, C = 0 } = scores;
  const center = size / 2;
  const radius = (size - 40) / 2;

  // Calculate points for the polygon
  const getPoint = (value, index) => {
    const angle = (index * 90 - 90) * (Math.PI / 180);
    const r = (value / 100) * radius;
    return {
      x: center + r * Math.cos(angle),
      y: center + r * Math.sin(angle)
    };
  };

  const values = [D, I, S, C];
  const idealValues = [IDEAL_LO_PROFILE.D, IDEAL_LO_PROFILE.I, IDEAL_LO_PROFILE.S, IDEAL_LO_PROFILE.C];

  const points = values.map((v, i) => getPoint(v, i));
  const idealPoints = idealValues.map((v, i) => getPoint(v, i));

  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z';
  const idealPathD = idealPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z';

  return (
    <div className="disc-radar-container">
      <svg width={size} height={size} className="disc-radar-svg">
        {/* Grid lines */}
        {[25, 50, 75, 100].map(level => (
          <polygon
            key={level}
            points={[0, 1, 2, 3].map(i => {
              const p = getPoint(level, i);
              return `${p.x},${p.y}`;
            }).join(' ')}
            fill="none"
            stroke="#e5e7eb"
            strokeWidth="1"
          />
        ))}

        {/* Axes */}
        {[0, 1, 2, 3].map(i => {
          const p = getPoint(100, i);
          return (
            <line
              key={i}
              x1={center}
              y1={center}
              x2={p.x}
              y2={p.y}
              stroke="#e5e7eb"
              strokeWidth="1"
            />
          );
        })}

        {/* Ideal profile */}
        {showIdeal && (
          <path
            d={idealPathD}
            fill="rgba(59, 130, 246, 0.1)"
            stroke="#3b82f6"
            strokeWidth="2"
            strokeDasharray="4 4"
          />
        )}

        {/* Candidate profile */}
        <path
          d={pathD}
          fill="rgba(16, 185, 129, 0.2)"
          stroke="#2D7A52"
          strokeWidth="2"
        />

        {/* Points */}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r="5"
            fill={DISC_STYLES[['D', 'I', 'S', 'C'][i]].color}
          />
        ))}

        {/* Labels */}
        {['D', 'I', 'S', 'C'].map((style, i) => {
          const labelPoint = getPoint(115, i);
          return (
            <text
              key={style}
              x={labelPoint.x}
              y={labelPoint.y}
              textAnchor="middle"
              dominantBaseline="middle"
              fill={DISC_STYLES[style].color}
              fontWeight="bold"
              fontSize="14"
            >
              {style}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

/**
 * DISC Style Card for detailed view
 */
export function DISCStyleCard({ style, score, isPrimary = false, isSecondary = false }) {
  const styleInfo = DISC_STYLES[style];

  return (
    <div className={`disc-style-card ${isPrimary ? 'primary' : ''} ${isSecondary ? 'secondary' : ''}`}>
      <div
        className="disc-style-card-header"
        style={{ backgroundColor: `${styleInfo.color}15` }}
      >
        <span
          className="disc-style-card-letter"
          style={{ color: styleInfo.color }}
        >
          {style}
        </span>
        <span className="disc-style-card-score">{score}</span>
      </div>
      <div className="disc-style-card-body">
        <h4 style={{ color: styleInfo.color }}>{styleInfo.label}</h4>
        <p>{styleInfo.description}</p>
        <div className="disc-style-traits">
          {styleInfo.traits.map(trait => (
            <span key={trait} className="disc-trait-tag">{trait}</span>
          ))}
        </div>
        <p className="disc-style-relevance">
          <strong>For LO Role:</strong> {styleInfo.loRelevance}
        </p>
      </div>
      {(isPrimary || isSecondary) && (
        <div
          className="disc-style-card-badge"
          style={{ backgroundColor: styleInfo.color }}
        >
          {isPrimary ? 'Primary' : 'Secondary'}
        </div>
      )}
    </div>
  );
}

export default DISCProfileChart;
