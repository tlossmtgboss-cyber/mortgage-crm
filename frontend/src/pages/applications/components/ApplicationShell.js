/**
 * ApplicationShell - Main wrapper component for mortgage applications
 * Provides progress bar, stage navigation, and layout structure
 */

import React, { useMemo, useState, useCallback, lazy, Suspense } from 'react';
import { useApplication } from '../contexts/ApplicationContext';
import { getStages, getVisibleStages, getStageById } from '../config/stageConfig';
import './ApplicationShell.css';
import '../../../../styles/borrower-theme.css';

// Lazy load DocumentsNeeded component for better performance
const DocumentsNeeded = lazy(() => import('./DocumentsNeeded'));

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
    workspaceSlug,
  } = state;

  // Document sidebar toggle state
  const [isChecklistExpanded, setIsChecklistExpanded] = useState(true);
  // Exit confirmation state (replaces window.confirm)
  const [showExitConfirm, setShowExitConfirm] = useState(false);

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

  // Stage progress percentage (0-100) — uses explicit progress values from stageConfig
  // so dynamic stage visibility changes (e.g., second_mortgage appearing) don't cause regression
  const stageProgress = useMemo(() => {
    if (currentStageIndex < 0 || !currentStageData) return 0;
    return currentStageData.progress || Math.round(((currentStageIndex + 1) / totalStages) * 100);
  }, [currentStageIndex, totalStages, currentStageData]);

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
  const handleExit = useCallback(() => {
    if (isDirty) {
      setShowExitConfirm(true);
      return;
    }
    onExit?.();
  }, [isDirty, onExit]);

  const confirmExit = useCallback(() => {
    setShowExitConfirm(false);
    onExit?.();
  }, [onExit]);

  const cancelExit = useCallback(() => {
    setShowExitConfirm(false);
  }, []);

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
    <div className="application-shell borrower-theme">
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

      {/* Exit confirmation banner */}
      {showExitConfirm && (
        <div className="exit-confirm-banner" role="alertdialog" aria-label="Confirm exit">
          <p>You have unsaved changes. Are you sure you want to leave?</p>
          <div className="exit-confirm-actions">
            <button type="button" className="btn-confirm-exit" onClick={confirmExit}>
              Leave
            </button>
            <button type="button" className="btn-cancel-exit" onClick={cancelExit}>
              Stay
            </button>
          </div>
        </div>
      )}

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
      {showDocumentChecklist && (
        <div className={`document-checklist-sidebar ${isChecklistExpanded ? 'expanded' : ''}`}>
          <button
            type="button"
            className="checklist-toggle"
            onClick={() => setIsChecklistExpanded(!isChecklistExpanded)}
            aria-expanded={isChecklistExpanded}
          >
            <span className="checklist-icon">📋</span>
            <span className="checklist-count">Documents Needed</span>
            <span className="toggle-arrow">{isChecklistExpanded ? '▼' : '▶'}</span>
          </button>

          {isChecklistExpanded && (
            <div className="checklist-content">
              <Suspense fallback={<div className="checklist-loading">Loading...</div>}>
                <DocumentsNeeded
                  applicationData={formData}
                  workspaceId={workspaceSlug}
                />
              </Suspense>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ApplicationShell;
