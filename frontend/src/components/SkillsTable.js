import React from 'react';
import './SkillsTable.css';

const SkillsTable = ({ skills, isManager, onAssess, onRemove }) => {
  const renderStars = (level) => {
    return '⭐'.repeat(level) + '☆'.repeat(5 - level);
  };

  const getGapColor = (gap) => {
    if (gap > 0) return 'ahead';
    if (gap === 0) return 'meeting';
    if (gap >= -1) return 'minor-gap';
    return 'major-gap';
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Not assessed';
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  return (
    <div className="skills-table-container">
      <table className="skills-table">
        <thead>
          <tr>
            <th>Skill</th>
            <th>Required</th>
            <th>Current</th>
            <th>Gap</th>
            <th>Last Assessed</th>
            {isManager && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {skills.map((skill) => (
            <tr key={skill.id} className={`row-${getGapColor(skill.gap)}`}>
              <td className="skill-name">
                {skill.skill_name}
                {skill.assessment_notes && (
                  <span className="has-notes" title={skill.assessment_notes}>
                    💬
                  </span>
                )}
              </td>
              <td className="proficiency-cell">
                <span className="stars">{renderStars(skill.required_proficiency)}</span>
                <span className="level-text">({skill.required_proficiency}/5)</span>
              </td>
              <td className="proficiency-cell">
                {skill.current_proficiency > 0 ? (
                  <>
                    <span className="stars">{renderStars(skill.current_proficiency)}</span>
                    <span className="level-text">({skill.current_proficiency}/5)</span>
                  </>
                ) : (
                  <span className="not-assessed">Not assessed</span>
                )}
              </td>
              <td className={`gap-cell ${getGapColor(skill.gap)}`}>
                {skill.gap > 0 && <span className="gap-badge ahead">+{skill.gap} ✓</span>}
                {skill.gap === 0 && <span className="gap-badge meeting">0 ✓</span>}
                {skill.gap < 0 && <span className="gap-badge gap">{skill.gap} ⚠️</span>}
              </td>
              <td className="date-cell">
                {formatDate(skill.assessed_at)}
              </td>
              {isManager && (
                <td className="actions-cell">
                  <button
                    onClick={() => onAssess(skill)}
                    className="btn-small btn-assess"
                  >
                    {skill.current_proficiency > 0 ? 'Re-assess' : 'Assess'}
                  </button>
                  <button
                    onClick={() => onRemove(skill.skill_id)}
                    className="btn-small btn-remove"
                  >
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default SkillsTable;
