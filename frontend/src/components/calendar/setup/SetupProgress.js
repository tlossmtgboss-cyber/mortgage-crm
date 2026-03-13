/**
 * Perennia AI - Calendar Setup Progress Indicator
 *
 * Horizontal stepper with numbered circles, connecting lines,
 * checkmarks for completed steps, and clickable navigation.
 * Renders a compact dot-only variant on mobile.
 */

import { useCallback } from 'react';

export default function SetupProgress({
  currentStep,
  totalSteps,
  completedSteps = [],
  skippedSteps = [],
  steps = [],
  onStepClick,
}) {
  const progressPercent = Math.round(((currentStep - 1) / (totalSteps - 1)) * 100);

  const getStepStatus = useCallback((stepNumber) => {
    if (stepNumber === currentStep) return 'active';
    if (completedSteps.includes(stepNumber)) return 'completed';
    if (skippedSteps.includes(stepNumber)) return 'skipped';
    return 'upcoming';
  }, [currentStep, completedSteps, skippedSteps]);

  const isClickable = useCallback((stepNumber) => {
    if (stepNumber === currentStep) return false;
    // Can click completed or skipped steps, or next available step
    return (
      completedSteps.includes(stepNumber) ||
      skippedSteps.includes(stepNumber) ||
      stepNumber <= Math.max(...completedSteps, 0) + 1
    );
  }, [currentStep, completedSteps, skippedSteps]);

  const handleClick = useCallback((stepNumber) => {
    if (isClickable(stepNumber) && onStepClick) {
      onStepClick(stepNumber);
    }
  }, [isClickable, onStepClick]);

  const handleKeyDown = useCallback((e, stepNumber) => {
    if ((e.key === 'Enter' || e.key === ' ') && isClickable(stepNumber)) {
      e.preventDefault();
      handleClick(stepNumber);
    }
  }, [isClickable, handleClick]);

  return (
    <div className="cal-setup-progress" role="navigation" aria-label="Setup progress">
      {/* Text header */}
      <div className="cal-setup-progress-header">
        <span className="cal-setup-progress-step-text">
          Step {currentStep} of {totalSteps}
        </span>
        <span className="cal-setup-progress-pct">
          {Math.round((completedSteps.length / totalSteps) * 100)}% Complete
        </span>
      </div>

      {/* Progress bar */}
      <div className="cal-setup-progress-bar" role="progressbar" aria-valuenow={progressPercent} aria-valuemin={0} aria-valuemax={100}>
        <div className="cal-setup-progress-bar-fill" style={{ width: `${progressPercent}%` }} />
      </div>

      {/* Desktop stepper: circles + labels */}
      <div className="cal-setup-stepper" aria-label="Setup steps">
        {/* Connecting line behind circles */}
        <div className="cal-setup-stepper-line" aria-hidden="true">
          <div className="cal-setup-stepper-line-fill" style={{ width: `${progressPercent}%` }} />
        </div>

        {steps.map((step) => {
          const status = getStepStatus(step.number);
          const clickable = isClickable(step.number);

          return (
            <div
              key={step.id}
              className={`cal-setup-stepper-item ${status} ${clickable ? 'clickable' : ''}`}
              onClick={() => handleClick(step.number)}
              onKeyDown={(e) => handleKeyDown(e, step.number)}
              tabIndex={clickable ? 0 : -1}
              role="button"
              aria-label={`${step.label}: ${status === 'completed' ? 'completed' : status === 'active' ? 'current step' : status === 'skipped' ? 'skipped' : 'upcoming'}`}
              aria-current={status === 'active' ? 'step' : undefined}
            >
              <div className="cal-setup-stepper-circle">
                {status === 'completed' ? (
                  <svg className="cal-setup-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : (
                  <span className="cal-setup-stepper-number">{step.number}</span>
                )}
              </div>
              <span className="cal-setup-stepper-label">{step.label}</span>
            </div>
          );
        })}
      </div>

      {/* Mobile compact dots */}
      <div className="cal-setup-dots" aria-hidden="true">
        {steps.map((step) => {
          const status = getStepStatus(step.number);
          return (
            <button
              key={step.id}
              className={`cal-setup-dot ${status}`}
              onClick={() => handleClick(step.number)}
              disabled={!isClickable(step.number)}
              tabIndex={-1}
              aria-hidden="true"
            />
          );
        })}
      </div>
    </div>
  );
}
