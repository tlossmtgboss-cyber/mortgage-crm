import React from 'react';
import './DISCGraphs.css';

/**
 * DISC dimension colors and info
 */
const DISC_COLORS = {
  D: { color: '#DC2626', label: 'Dominance', short: 'D' },
  I: { color: '#F59E0B', label: 'Influence', short: 'I' },
  S: { color: '#2D7A52', label: 'Steadiness', short: 'S' },
  C: { color: '#3B82F6', label: 'Conscientiousness', short: 'C' }
};

/**
 * DISCGraphs Component
 * Shows Adapted Style (Graph I) and Natural Style (Graph II) side by side
 */
function DISCGraphs({
  adaptedScores = {},
  naturalScores = {},
  adaptedStyle = '',
  naturalStyle = '',
  showLabels = true,
  compact = false
}) {
  const dimensions = ['D', 'I', 'S', 'C'];

  const renderGraph = (scores, title, style, graphNum) => (
    <div className={`disc-graph ${compact ? 'compact' : ''}`}>
      <div className="disc-graph-header">
        <span className="disc-graph-title">{title}</span>
        <span className="disc-graph-num">Graph {graphNum}</span>
      </div>

      <div className="disc-graph-bars">
        {dimensions.map(dim => {
          const score = scores[dim] || scores[dim.toLowerCase()] || 0;
          const info = DISC_COLORS[dim];

          return (
            <div key={dim} className="disc-graph-bar-container">
              <div className="disc-graph-bar-wrapper">
                <div
                  className="disc-graph-bar"
                  style={{
                    height: `${score}%`,
                    backgroundColor: info.color
                  }}
                />
              </div>
              <span
                className="disc-graph-bar-label"
                style={{ color: info.color }}
              >
                {dim}
              </span>
              <span className="disc-graph-bar-value">{score}</span>
            </div>
          );
        })}
      </div>

      <div className="disc-graph-footer">
        <span className="disc-graph-style">{style}</span>
        {showLabels && (
          <span className="disc-graph-style-desc">
            {getStyleDescription(style)}
          </span>
        )}
      </div>
    </div>
  );

  return (
    <div className="disc-graphs-container">
      {renderGraph(adaptedScores, 'Adapted Style', adaptedStyle, 'I')}
      <div className="disc-graphs-divider" />
      {renderGraph(naturalScores, 'Natural Style', naturalStyle, 'II')}

      <div className="disc-graphs-combined">
        <span className="disc-combined-label">Combined Style:</span>
        <span className="disc-combined-style">{adaptedStyle}/{naturalStyle}</span>
      </div>
    </div>
  );
}

/**
 * Get description for a style code
 */
function getStyleDescription(style) {
  const descriptions = {
    'D': 'Driver',
    'Di': 'Driver-Influencer',
    'Dc': 'Driver-Analyst',
    'I': 'Influencer',
    'Id': 'Influencer-Driver',
    'Is': 'Influencer-Supporter',
    'S': 'Supporter',
    'Si': 'Supporter-Influencer',
    'Sc': 'Supporter-Analyst',
    'C': 'Analyst',
    'Cd': 'Analyst-Driver',
    'Cs': 'Analyst-Supporter'
  };
  return descriptions[style] || style;
}

/**
 * Single DISC Bar Chart (for standalone use)
 */
export function DISCBarChart({
  scores = {},
  title = 'DISC Profile',
  showValues = true,
  height = 200
}) {
  const dimensions = ['D', 'I', 'S', 'C'];
  const maxScore = Math.max(...dimensions.map(d => scores[d] || scores[d.toLowerCase()] || 0), 100);

  return (
    <div className="disc-bar-chart" style={{ height }}>
      <div className="disc-bar-chart-title">{title}</div>
      <div className="disc-bar-chart-container">
        {dimensions.map(dim => {
          const score = scores[dim] || scores[dim.toLowerCase()] || 0;
          const info = DISC_COLORS[dim];
          const heightPct = (score / maxScore) * 100;

          return (
            <div key={dim} className="disc-bar-item">
              <div className="disc-bar-column">
                <div
                  className="disc-bar-fill"
                  style={{
                    height: `${heightPct}%`,
                    backgroundColor: info.color
                  }}
                />
              </div>
              <span className="disc-bar-dim" style={{ color: info.color }}>{dim}</span>
              {showValues && <span className="disc-bar-score">{score}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default DISCGraphs;
