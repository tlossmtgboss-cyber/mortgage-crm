import React, { useState } from 'react';
import { getGrade, GradeBar, GradeBadge } from './CandidateGradeCircle';
import './AssessmentScoreCard.css';

/**
 * Category configurations with weights and sub-components
 */
const CATEGORY_CONFIG = {
  production: {
    label: 'Production',
    weight: 0.45,
    weightLabel: '45%',
    icon: '📊',
    description: 'Volume, units, consistency, growth trend',
    subComponents: [
      { key: 'annual_volume_score', label: 'Annual Volume' },
      { key: 'annual_units_score', label: 'Annual Units' },
      { key: 'consistency_score', label: 'Consistency' },
      { key: 'growth_trend_score', label: 'Growth Trend' }
    ]
  },
  disc: {
    label: 'Personality (DISC)',
    weight: 0.20,
    weightLabel: '20%',
    icon: '🧠',
    description: 'D-I-S-C profile fit for LO role',
    subComponents: [
      { key: 'd_score', label: 'Dominance' },
      { key: 'i_score', label: 'Influence' },
      { key: 's_score', label: 'Steadiness' },
      { key: 'c_score', label: 'Conscientiousness' }
    ]
  },
  character: {
    label: 'Character',
    weight: 0.15,
    weightLabel: '15%',
    icon: '⭐',
    description: 'Integrity, coachability, resilience, work ethic',
    subComponents: [
      { key: 'integrity_score', label: 'Integrity' },
      { key: 'coachability_score', label: 'Coachability' },
      { key: 'resilience_score', label: 'Resilience' },
      { key: 'work_ethic_score', label: 'Work Ethic' }
    ]
  },
  skills: {
    label: 'Skills',
    weight: 0.10,
    weightLabel: '10%',
    icon: '🛠️',
    description: 'Technical, product knowledge, market expertise',
    subComponents: [
      { key: 'technical_score', label: 'Technical' },
      { key: 'product_knowledge_score', label: 'Product Knowledge' },
      { key: 'market_expertise_score', label: 'Market Expertise' },
      { key: 'technology_proficiency_score', label: 'Technology' }
    ]
  },
  culture_fit: {
    label: 'Culture Fit',
    weight: 0.10,
    weightLabel: '10%',
    icon: '🤝',
    description: 'Values alignment, team compatibility',
    subComponents: [
      { key: 'values_alignment_score', label: 'Values Alignment' },
      { key: 'team_compatibility_score', label: 'Team Compatibility' },
      { key: 'communication_style_score', label: 'Communication' },
      { key: 'growth_mindset_score', label: 'Growth Mindset' }
    ]
  }
};

/**
 * Individual score card for a grading category
 */
function AssessmentScoreCard({
  category,
  score,
  grade,
  breakdown = {},
  isEditable = false,
  onEdit,
  isExpanded: controlledExpanded,
  onToggleExpand
}) {
  const [localExpanded, setLocalExpanded] = useState(false);
  const config = CATEGORY_CONFIG[category];

  if (!config) return null;

  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : localExpanded;
  const toggleExpand = onToggleExpand || (() => setLocalExpanded(!localExpanded));

  const { color } = getGrade(score);
  const contribution = (score || 0) * config.weight;

  return (
    <div className={`assessment-score-card ${isExpanded ? 'expanded' : ''}`}>
      <div className="score-card-header" onClick={toggleExpand}>
        <div className="score-card-left">
          <span className="score-card-icon">{config.icon}</span>
          <div className="score-card-info">
            <span className="score-card-label">{config.label}</span>
            <span className="score-card-weight">{config.weightLabel} weight</span>
          </div>
        </div>
        <div className="score-card-right">
          <div className="score-card-scores">
            <GradeBar score={score} height={10} />
          </div>
          <GradeBadge score={score} grade={grade} size="md" />
          <button
            className="score-card-expand-btn"
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
          >
            {isExpanded ? '▲' : '▼'}
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="score-card-details">
          <p className="score-card-description">{config.description}</p>

          <div className="score-card-contribution">
            <span>Contribution to Overall:</span>
            <strong>{contribution.toFixed(1)} pts</strong>
          </div>

          {config.subComponents.length > 0 && (
            <div className="score-card-breakdown">
              <h5>Score Breakdown</h5>
              <div className="breakdown-grid">
                {config.subComponents.map(sub => {
                  const subScore = breakdown[sub.key];
                  const subGrade = getGrade(subScore);
                  return (
                    <div key={sub.key} className="breakdown-item">
                      <div className="breakdown-item-header">
                        <span className="breakdown-label">{sub.label}</span>
                        <span
                          className="breakdown-value"
                          style={{ color: subGrade.color }}
                        >
                          {subScore ?? '-'}
                        </span>
                      </div>
                      <div className="breakdown-bar">
                        <div
                          className="breakdown-bar-fill"
                          style={{
                            width: `${subScore || 0}%`,
                            backgroundColor: subGrade.color
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {breakdown.notes && (
            <div className="score-card-notes">
              <h5>Notes</h5>
              <p>{breakdown.notes}</p>
            </div>
          )}

          {isEditable && (
            <button
              className="score-card-edit-btn"
              onClick={(e) => {
                e.stopPropagation();
                // Pass explicit category object with all needed properties
                const categoryData = {
                  key: category,
                  label: config.label,
                  description: config.description,
                  weight: config.weight,
                  weightLabel: config.weightLabel
                };
                console.log('[AssessmentScoreCard] Passing category:', categoryData);
                onEdit && onEdit(categoryData);
              }}
            >
              Edit Scores
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Grid of all assessment score cards
 */
export function AssessmentScoreGrid({
  assessment,
  isEditable = false,
  onEditCategory
}) {
  const [expandedCategory, setExpandedCategory] = useState(null);

  const categories = [
    { key: 'production', data: assessment?.production },
    { key: 'disc', data: assessment?.disc ? { ...assessment.disc, score: assessment.disc.composite_score } : null },
    { key: 'character', data: assessment?.character },
    { key: 'skills', data: assessment?.skills },
    { key: 'culture_fit', data: assessment?.culture_fit }
  ];

  return (
    <div className="assessment-score-grid">
      {categories.map(({ key, data }) => (
        <AssessmentScoreCard
          key={key}
          category={key}
          score={data?.score}
          grade={data?.grade}
          breakdown={data?.breakdown || data || {}}
          isEditable={isEditable}
          onEdit={onEditCategory}
          isExpanded={expandedCategory === key}
          onToggleExpand={() => setExpandedCategory(expandedCategory === key ? null : key)}
        />
      ))}
    </div>
  );
}

/**
 * Compact view showing just scores and grades
 */
export function AssessmentScoreSummary({ assessment }) {
  const categories = [
    { key: 'production', label: 'Production', score: assessment?.production?.score, grade: assessment?.production?.grade },
    { key: 'disc', label: 'DISC', score: assessment?.disc?.composite_score, grade: assessment?.disc?.grade },
    { key: 'character', label: 'Character', score: assessment?.character?.score, grade: assessment?.character?.grade },
    { key: 'skills', label: 'Skills', score: assessment?.skills?.score, grade: assessment?.skills?.grade },
    { key: 'culture_fit', label: 'Culture', score: assessment?.culture_fit?.score, grade: assessment?.culture_fit?.grade }
  ];

  return (
    <div className="assessment-score-summary">
      {categories.map(({ key, label, score, grade }) => {
        const { color } = getGrade(score);
        return (
          <div key={key} className="summary-item">
            <span className="summary-label">{label}</span>
            <div className="summary-bar">
              <div
                className="summary-bar-fill"
                style={{ width: `${score || 0}%`, backgroundColor: color }}
              />
            </div>
            <span className="summary-score" style={{ color }}>{score?.toFixed(0) || '-'}</span>
            <GradeBadge score={score} grade={grade} size="sm" />
          </div>
        );
      })}
    </div>
  );
}

export default AssessmentScoreCard;
