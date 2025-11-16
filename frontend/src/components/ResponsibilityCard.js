import React from 'react';
import './ResponsibilityCard.css';

/**
 * ResponsibilityCard - Individual responsibility display card
 *
 * Features:
 * - Draggable card with drag handle
 * - Priority color coding
 * - Skills tags display
 * - Ownership and time allocation display
 * - Edit and Archive actions
 */

function ResponsibilityCard({ responsibility, onEdit, onArchive, provided }) {
  const formatDate = (dateString) => {
    if (!dateString) return null;
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const getPriorityClass = (priority) => {
    const classes = {
      'critical': 'priority-critical',
      'high': 'priority-high',
      'medium': 'priority-medium',
      'low': 'priority-low'
    };
    return classes[priority] || 'priority-medium';
  };

  const getOwnershipDisplay = (ownership) => {
    const displays = {
      'primary': { text: 'Primary', icon: '⭐', class: 'ownership-primary' },
      'secondary': { text: 'Secondary', icon: '➕', class: 'ownership-secondary' },
      'shared': { text: 'Shared', icon: '🤝', class: 'ownership-shared' }
    };
    return displays[ownership] || displays['primary'];
  };

  const ownershipInfo = getOwnershipDisplay(responsibility.ownership);

  return (
    <div
      className="responsibility-card"
      ref={provided.innerRef}
      {...provided.draggableProps}
    >
      <div className="card-header">
        <div className="drag-handle" {...provided.dragHandleProps}>
          <span className="drag-icon">⋮⋮</span>
        </div>
        <h4 className="card-title">
          <span className="title-icon">📋</span>
          {responsibility.title}
        </h4>
        <div className="card-actions">
          <button onClick={onEdit} className="btn-card-edit" title="Edit">
            ✏️
          </button>
          <button onClick={onArchive} className="btn-card-archive" title="Archive">
            🗄️
          </button>
        </div>
      </div>

      <div className="card-body">
        {/* Ownership and Time Allocation Row */}
        <div className="card-row">
          <div className="info-item">
            <span className="label">Ownership:</span>
            <span className={`ownership-badge ${ownershipInfo.class}`}>
              <span className="ownership-icon">{ownershipInfo.icon}</span>
              {ownershipInfo.text}
            </span>
          </div>
          <div className="info-item">
            <span className="label">Time:</span>
            <span className="value">{responsibility.time_allocation || 0}%</span>
          </div>
        </div>

        {/* Priority Row */}
        <div className="card-row">
          <div className="info-item">
            <span className="label">Priority:</span>
            <span className={`priority-badge ${getPriorityClass(responsibility.priority)}`}>
              {responsibility.priority}
            </span>
          </div>
        </div>

        {/* Skills Row */}
        {responsibility.required_skills && responsibility.required_skills.length > 0 && (
          <div className="card-row">
            <span className="label">Required Skills:</span>
            <div className="skills-tags">
              {responsibility.required_skills.slice(0, 5).map(skill => (
                <span key={skill.id} className="skill-tag">
                  {skill.name}
                </span>
              ))}
              {responsibility.required_skills.length > 5 && (
                <span className="skill-tag more-skills">
                  +{responsibility.required_skills.length - 5} more
                </span>
              )}
            </div>
          </div>
        )}

        {/* Description Row */}
        {responsibility.description && (
          <div className="card-row">
            <span className="label">Description:</span>
            <p className="description">
              {responsibility.description.length > 200
                ? `${responsibility.description.substring(0, 200)}...`
                : responsibility.description
              }
            </p>
          </div>
        )}

        {/* Effective Date Row */}
        <div className="card-row">
          <div className="info-item">
            <span className="label">Effective:</span>
            <span className="date-range">
              {formatDate(responsibility.effective_date)}
              {' - '}
              {responsibility.end_date ? formatDate(responsibility.end_date) : 'Present'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ResponsibilityCard;
