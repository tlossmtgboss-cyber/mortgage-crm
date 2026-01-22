/**
 * JR LO Tab Component
 *
 * Displays the Junior Loan Officer's 5 C's analysis:
 * - Credit, Collateral, Capacity, Characteristics, Cash
 *
 * Also includes:
 * - Documents Requested List
 * - Items to Address (review tasks)
 */

import React from 'react';
import FiveCCard from './FiveCCard';

const JRLOTab = ({ fiveCAnalysis, documentRequests, reviewTasks, onCreateTask }) => {
  // Extract 5 C's data from artifacts
  const creditData = fiveCAnalysis?.find(a => a.artifact_type === 'five_c_credit')?.structured_data;
  const collateralData = fiveCAnalysis?.find(a => a.artifact_type === 'five_c_collateral')?.structured_data;
  const capacityData = fiveCAnalysis?.find(a => a.artifact_type === 'five_c_capacity')?.structured_data;
  const characteristicsData = fiveCAnalysis?.find(a => a.artifact_type === 'five_c_characteristics')?.structured_data;
  const cashData = fiveCAnalysis?.find(a => a.artifact_type === 'five_c_cash')?.structured_data;

  const hasFiveCData = creditData || collateralData || capacityData || characteristicsData || cashData;

  if (!hasFiveCData && (!documentRequests || documentRequests.length === 0)) {
    return (
      <div className="jrlo-tab">
        <div className="summary-card">
          <p style={{ color: '#6b7280', textAlign: 'center', padding: '20px' }}>
            No JR LO analysis available for this call.
          </p>
        </div>
      </div>
    );
  }

  // Calculate overall assessment
  const assessments = [
    creditData?.assessment,
    collateralData?.assessment,
    capacityData?.assessment,
    characteristicsData?.assessment,
    cashData?.assessment,
  ].filter(Boolean);

  const weakCount = assessments.filter(a => a === 'Weak').length;
  const strongCount = assessments.filter(a => a === 'Strong').length;

  let overallIndicator = 'neutral';
  if (weakCount >= 2) overallIndicator = 'negative';
  else if (strongCount >= 4) overallIndicator = 'positive';

  return (
    <div className="jrlo-tab">
      {/* Overall Assessment Header */}
      {hasFiveCData && (
        <div className="five-c-header">
          <h3>5 C's of Credit Analysis</h3>
          <div className={`overall-indicator ${overallIndicator}`}>
            {strongCount > 0 && <span className="count strong">{strongCount} Strong</span>}
            {assessments.filter(a => a === 'Adequate').length > 0 && (
              <span className="count adequate">
                {assessments.filter(a => a === 'Adequate').length} Adequate
              </span>
            )}
            {weakCount > 0 && <span className="count weak">{weakCount} Weak</span>}
          </div>
        </div>
      )}

      {/* 5 C's Grid */}
      {hasFiveCData && (
        <div className="five-c-grid">
          {creditData && (
            <FiveCCard
              category="credit"
              data={creditData}
              onCreateTask={onCreateTask}
            />
          )}
          {collateralData && (
            <FiveCCard
              category="collateral"
              data={collateralData}
              onCreateTask={onCreateTask}
            />
          )}
          {capacityData && (
            <FiveCCard
              category="capacity"
              data={capacityData}
              onCreateTask={onCreateTask}
            />
          )}
          {characteristicsData && (
            <FiveCCard
              category="characteristics"
              data={characteristicsData}
              onCreateTask={onCreateTask}
            />
          )}
          {cashData && (
            <FiveCCard
              category="cash"
              data={cashData}
              onCreateTask={onCreateTask}
            />
          )}
        </div>
      )}

      {/* Documents Requested */}
      {documentRequests && documentRequests.length > 0 && (
        <div className="summary-card jrlo-documents">
          <h4>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="12" y1="18" x2="12" y2="12" />
              <line x1="9" y1="15" x2="15" y2="15" />
            </svg>
            Documents Requested ({documentRequests.length})
          </h4>
          <div className="documents-list">
            {documentRequests.map((doc, index) => (
              <div key={doc.id || index} className={`document-item priority-${doc.priority || 'medium'}`}>
                <div className="doc-header">
                  <span className="doc-name">
                    {doc.title || doc.structured_data?.document_name || 'Document'}
                  </span>
                  <span className={`priority-badge ${doc.priority || 'medium'}`}>
                    {doc.priority || 'medium'}
                  </span>
                </div>
                <div className="doc-reason">
                  {doc.content || doc.structured_data?.reason || ''}
                </div>
                {doc.structured_data?.loan_program_required && (
                  <span className="required-badge">Program Required</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Review Items / Tasks */}
      {reviewTasks && reviewTasks.length > 0 && (
        <div className="summary-card jrlo-review-items" style={{ background: '#fef3c7', borderLeft: '3px solid #f59e0b' }}>
          <h4 style={{ color: '#92400e' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            Items to Address ({reviewTasks.length})
          </h4>
          <div className="review-items-list">
            {reviewTasks.map((task, index) => (
              <div key={task.id || index} className="review-item">
                <div className="review-item-content">
                  <span className="review-category">
                    {task.structured_data?.category || 'General'}
                  </span>
                  <span className="review-title">{task.title}</span>
                  <span className="review-action">{task.content || task.structured_data?.action_required}</span>
                </div>
                {onCreateTask && (
                  <button
                    className="review-task-btn"
                    onClick={() => onCreateTask({
                      task_type: 'jrlo_5c_review',
                      title: task.title,
                      description: task.content || task.structured_data?.action_required || '',
                      priority: task.priority || 'medium',
                      assigned_role: 'lo',
                    })}
                  >
                    Create Task
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default JRLOTab;
