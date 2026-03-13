/**
 * Perennia AI - Calendar Setup Step Wrapper
 *
 * Provides a consistent layout for each setup step:
 *   - Step title and description
 *   - Content area for the step component
 *   - "Skip this step" link
 *   - "Need help?" tooltip with step-specific guidance
 */

import { useState, useCallback, useRef, useEffect } from 'react';

export default function SetupStepWrapper({
  step,
  currentStep,
  totalSteps,
  canSkip = false,
  onSkip,
  children,
}) {
  const [showHelp, setShowHelp] = useState(false);
  const helpRef = useRef(null);
  const helpBtnRef = useRef(null);

  // Close help tooltip when clicking outside
  useEffect(() => {
    if (!showHelp) return;

    function handleClickOutside(e) {
      if (
        helpRef.current && !helpRef.current.contains(e.target) &&
        helpBtnRef.current && !helpBtnRef.current.contains(e.target)
      ) {
        setShowHelp(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showHelp]);

  // Close help on Escape
  useEffect(() => {
    if (!showHelp) return;

    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        setShowHelp(false);
        helpBtnRef.current?.focus();
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [showHelp]);

  const toggleHelp = useCallback(() => {
    setShowHelp(prev => !prev);
  }, []);

  if (!step) return null;

  return (
    <div className="cal-setup-step-wrapper">
      {/* Step header */}
      <div className="cal-setup-step-header">
        <div className="cal-setup-step-title-row">
          <div className="cal-setup-step-icon" aria-hidden="true">
            <i className={`fas ${step.icon}`}></i>
          </div>
          <div className="cal-setup-step-title-group">
            <h2 className="cal-setup-step-title">{step.title}</h2>
            <p className="cal-setup-step-description">{step.description}</p>
          </div>
        </div>

        <div className="cal-setup-step-actions">
          {/* Help tooltip */}
          {step.helpText && (
            <div className="cal-setup-help-container">
              <button
                ref={helpBtnRef}
                className="cal-setup-help-btn"
                onClick={toggleHelp}
                aria-expanded={showHelp}
                aria-haspopup="true"
                aria-label="Need help with this step?"
              >
                <i className="fas fa-question-circle"></i>
                <span className="cal-setup-help-label">Need help?</span>
              </button>
              {showHelp && (
                <div
                  ref={helpRef}
                  className="cal-setup-help-tooltip"
                  role="tooltip"
                >
                  <div className="cal-setup-help-tooltip-arrow" />
                  <p>{step.helpText}</p>
                </div>
              )}
            </div>
          )}

          {/* Skip link */}
          {canSkip && onSkip && (
            <button
              className="cal-setup-skip-btn"
              onClick={onSkip}
              aria-label={`Skip ${step.title} step`}
            >
              Skip this step <i className="fas fa-forward"></i>
            </button>
          )}
        </div>
      </div>

      {/* Step content */}
      <div className="cal-setup-step-content">
        {children}
      </div>
    </div>
  );
}
