import React, { useState } from 'react';
import KeyResultProgress from './KeyResultProgress';
import SelfAssessmentModal from './SelfAssessmentModal';
import ManagerAssessmentModal from './ManagerAssessmentModal';
import './GoalCard.css';

const GoalCard = ({ goal, userId, isManager, onEdit, onDelete, onKeyResultUpdate, onRefresh }) => {
  const [showSelfAssessment, setShowSelfAssessment] = useState(false);
  const [showManagerAssessment, setShowManagerAssessment] = useState(false);
  const [expandedAssessments, setExpandedAssessments] = useState(false);

  const getStatusIcon = (status) => {
    const icons = {
      not_started: '⚪',
      on_track: '✅',
      at_risk: '⚠️',
      blocked: '🚫',
      ahead: '🚀',
      completed: '✅'
    };
    return icons[status] || '⚪';
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  const calculateOverallProgress = () => {
    if (!goal.key_results || goal.key_results.length === 0) return 0;
    const total = goal.key_results.reduce((sum, kr) => {
      const progress = (kr.current / kr.target) * 100;
      return sum + Math.min(progress, 100);
    }, 0);
    return Math.round(total / goal.key_results.length);
  };

  return (
    <div className={`goal-card status-${goal.status}`}>
      {/* Header */}
      <div className="goal-header">
        <div className="goal-title-row">
          <span className="goal-icon">🎯</span>
          <h4 className="goal-objective">{goal.objective}</h4>
        </div>
        <div className="goal-actions">
          {isManager && (
            <>
              <button onClick={onEdit} className="btn-icon" title="Edit goal">
                ✏️
              </button>
              <button onClick={onDelete} className="btn-icon" title="Delete goal">
                🗑️
              </button>
            </>
          )}
        </div>
      </div>

      {/* Status and Period */}
      <div className="goal-meta">
        <span className={`status-badge status-${goal.status}`}>
          {getStatusIcon(goal.status)} {goal.status.replace('_', ' ')}
        </span>
        <span className="goal-period">
          {formatDate(goal.start_date)} - {formatDate(goal.end_date)}
        </span>
        <span className="overall-progress">
          Overall: {calculateOverallProgress()}%
        </span>
      </div>

      {/* Key Results */}
      <div className="key-results-section">
        <h5>Key Results:</h5>
        {goal.key_results && goal.key_results.length > 0 ? (
          goal.key_results.map((kr, index) => (
            <KeyResultProgress
              key={kr.id}
              keyResult={kr}
              index={index}
              isManager={isManager}
              onUpdate={(value) => onKeyResultUpdate(kr.id, value)}
            />
          ))
        ) : (
          <p className="empty-message">No key results defined</p>
        )}
      </div>

      {/* Assessments */}
      <div className="assessments-section">
        <button
          className="assessments-toggle"
          onClick={() => setExpandedAssessments(!expandedAssessments)}
        >
          {expandedAssessments ? '▼' : '▶'} Assessments
        </button>

        {expandedAssessments && (
          <div className="assessments-content">
            {/* Employee Self-Assessment */}
            <div className="assessment-block employee-assessment">
              <div className="assessment-header">
                <h6>👤 Employee Self-Assessment</h6>
                {!isManager && (
                  <button
                    onClick={() => setShowSelfAssessment(true)}
                    className="btn-small btn-secondary"
                  >
                    {goal.employee_assessment ? 'Update' : 'Add'} Assessment
                  </button>
                )}
              </div>
              {goal.employee_assessment ? (
                <div className="assessment-content">
                  {goal.employee_assessment.progress_percent !== null && (
                    <p><strong>Progress:</strong> {goal.employee_assessment.progress_percent}%</p>
                  )}
                  {goal.employee_assessment.achievements && (
                    <p><strong>Achievements:</strong> {goal.employee_assessment.achievements}</p>
                  )}
                  {goal.employee_assessment.challenges && (
                    <p><strong>Challenges:</strong> {goal.employee_assessment.challenges}</p>
                  )}
                  {goal.employee_assessment.support_needed && (
                    <p><strong>Support Needed:</strong> {goal.employee_assessment.support_needed}</p>
                  )}
                  {goal.employee_assessment.updated_at && (
                    <span className="assessment-date">
                      Updated: {formatDate(goal.employee_assessment.updated_at)}
                    </span>
                  )}
                </div>
              ) : (
                <p className="no-assessment">No self-assessment yet</p>
              )}
            </div>

            {/* Manager Assessment */}
            <div className="assessment-block manager-assessment">
              <div className="assessment-header">
                <h6>👨‍💼 Manager Assessment</h6>
                {isManager && (
                  <button
                    onClick={() => setShowManagerAssessment(true)}
                    className="btn-small btn-secondary"
                  >
                    {goal.manager_assessment ? 'Update' : 'Add'} Feedback
                  </button>
                )}
              </div>
              {goal.manager_assessment ? (
                <div className="assessment-content">
                  <p>{goal.manager_assessment.notes || 'No feedback yet'}</p>
                  {goal.manager_assessment.updated_at && (
                    <span className="assessment-date">
                      Updated: {formatDate(goal.manager_assessment.updated_at)}
                    </span>
                  )}
                </div>
              ) : (
                <p className="no-assessment">No manager feedback yet</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Modals */}
      {showSelfAssessment && (
        <SelfAssessmentModal
          goal={goal}
          userId={userId}
          onClose={() => setShowSelfAssessment(false)}
          onSave={onRefresh}
        />
      )}

      {showManagerAssessment && (
        <ManagerAssessmentModal
          goal={goal}
          userId={userId}
          onClose={() => setShowManagerAssessment(false)}
          onSave={onRefresh}
        />
      )}
    </div>
  );
};

export default GoalCard;
