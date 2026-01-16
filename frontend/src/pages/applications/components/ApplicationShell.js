/**
 * ApplicationShell - Main wrapper component for mortgage applications
 * Provides progress bar, stage navigation, and layout structure
 */

import React, { useMemo, useState } from 'react';
import { useApplication } from '../contexts/ApplicationContext';
import { getStages, getVisibleStages, getStageById } from '../config/stageConfig';
import { useDocumentChecklist } from '../hooks/useDocumentChecklist';
import './ApplicationShell.css';

const ApplicationShell = ({
  children,
  onExit,
  showSaveIndicator = true,
  showDocumentChecklist = true,
}) => {
  const { state, actions, computed } = useApplication();
  const {
    applicationType,
    currentStage,
    currentQuestionIndex,
    formData,
    isDirty,
  } = state;

  // Document checklist state
  const [isChecklistExpanded, setIsChecklistExpanded] = useState(false);
  const { requiredDocuments, categories, totalRequired } = useDocumentChecklist(formData);

  // Get stages based on application type
  const allStages = useMemo(() => getStages(applicationType), [applicationType]);
  const visibleStages = useMemo(
    () => getVisibleStages(applicationType, formData),
    [applicationType, formData]
  );
  const currentStageData = useMemo(
    () => getStageById(applicationType, currentStage),
    [applicationType, currentStage]
  );

  // Calculate progress
  const currentStageIndex = visibleStages.findIndex(s => s.id === currentStage);
  const totalStages = visibleStages.length;

  // Stage progress percentage (0-100)
  const stageProgress = useMemo(() => {
    if (currentStageIndex < 0) return 0;
    return Math.round((currentStageIndex / totalStages) * 100);
  }, [currentStageIndex, totalStages]);

  // Handle stage click (for navigation)
  const handleStageClick = (stageId) => {
    const targetIndex = visibleStages.findIndex(s => s.id === stageId);
    const currentIndex = currentStageIndex;

    // Only allow going to completed stages or current stage
    if (targetIndex <= currentIndex) {
      actions.setStage(stageId);
      actions.setQuestionIndex(0);
    }
  };

  // Handle exit
  const handleExit = () => {
    if (isDirty) {
      const confirmed = window.confirm(
        'You have unsaved changes. Are you sure you want to leave?'
      );
      if (!confirmed) return;
    }
    onExit?.();
  };

  // Get icon for stage
  const getStageIcon = (icon) => {
    const iconMap = {
      user: '👤',
      home: '🏠',
      document: '📄',
      dollar: '💵',
      bank: '🏦',
      building: '🏢',
      clipboard: '📋',
      chart: '📊',
      calendar: '📅',
      check: '✓',
    };
    return iconMap[icon] || '•';
  };

  return (
    <div className="application-shell">
      {/* Header */}
      <header className="application-header">
        <div className="application-header-content">
          <button
            type="button"
            className="application-exit-btn"
            onClick={handleExit}
            aria-label="Exit application"
          >
            ← Back
          </button>

          <div className="application-title">
            <h1>{applicationType === 'purchase' ? 'Purchase' : 'Refinance'} Application</h1>
            {currentStageData && (
              <span className="current-stage-label">{currentStageData.label}</span>
            )}
          </div>

          {showSaveIndicator && (
            <div className="save-indicator">
              {isDirty ? (
                <span className="save-status unsaved">Saving...</span>
              ) : (
                <span className="save-status saved">Saved ✓</span>
              )}
            </div>
          )}
        </div>

        {/* Progress bar */}
        <div className="progress-container">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${stageProgress}%` }}
            />
          </div>
          <span className="progress-text">{stageProgress}% Complete</span>
        </div>
      </header>

      {/* Stage indicators (desktop) */}
      <nav className="stage-nav" aria-label="Application stages">
        <div className="stage-list">
          {visibleStages.map((stage, index) => {
            const isCompleted = index < currentStageIndex;
            const isCurrent = stage.id === currentStage;
            const isClickable = index <= currentStageIndex;

            return (
              <button
                key={stage.id}
                type="button"
                className={`stage-item ${isCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''}`}
                onClick={() => isClickable && handleStageClick(stage.id)}
                disabled={!isClickable}
                aria-current={isCurrent ? 'step' : undefined}
              >
                <span className="stage-indicator">
                  {isCompleted ? '✓' : getStageIcon(stage.icon)}
                </span>
                <span className="stage-label">{stage.shortLabel || stage.label}</span>
              </button>
            );
          })}
        </div>
      </nav>

      {/* Main content area */}
      <main className="application-main">
        <div className="application-content">
          {children}
        </div>
      </main>

      {/* Mobile stage indicator */}
      <div className="mobile-stage-indicator">
        <span className="mobile-stage-current">
          Step {currentStageIndex + 1} of {totalStages}
        </span>
        <span className="mobile-stage-name">
          {currentStageData?.label}
        </span>
      </div>

      {/* Dynamic Document Checklist */}
      {showDocumentChecklist && totalRequired > 0 && (
        <div className={`document-checklist-sidebar ${isChecklistExpanded ? 'expanded' : ''}`}>
          <button
            type="button"
            className="checklist-toggle"
            onClick={() => setIsChecklistExpanded(!isChecklistExpanded)}
            aria-expanded={isChecklistExpanded}
          >
            <span className="checklist-icon">📋</span>
            <span className="checklist-count">{totalRequired} Documents Needed</span>
            <span className="toggle-arrow">{isChecklistExpanded ? '▼' : '▶'}</span>
          </button>

          {isChecklistExpanded && (
            <div className="checklist-content">
              <p className="checklist-intro">
                Based on your answers, you'll need to provide these documents:
              </p>

              {Object.entries(categories).map(([category, docs]) => (
                docs.length > 0 && (
                  <div key={category} className="checklist-category">
                    <h4 className="category-title">{category}</h4>
                    <ul className="document-list">
                      {docs.map((doc) => (
                        <li key={doc.id} className={`document-item ${doc.priority === 'high' ? 'high-priority' : ''}`}>
                          <span className="doc-name">{doc.name}</span>
                          {doc.description && (
                            <span className="doc-description">{doc.description}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )
              ))}

              <div className="checklist-footer">
                <p className="checklist-note">
                  You'll be able to upload these after completing the application.
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ApplicationShell;
