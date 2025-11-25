import React from 'react';
import './ProgressIndicator.css';

const ProgressIndicator = ({ currentStep, totalSteps }) => {
  const progressPercentage = (currentStep / totalSteps) * 100;

  // Dynamic step names based on totalSteps
  const stepConfigs = {
    5: [
      { number: 1, name: 'Registration' },
      { number: 2, name: 'Profile' },
      { number: 3, name: 'AI Setup' },
      { number: 4, name: 'Training' },
      { number: 5, name: 'Confirm' }
    ],
    10: [
      { number: 1, name: 'Registration' },
      { number: 2, name: 'Business Info' },
      { number: 3, name: 'Team Setup' },
      { number: 4, name: 'Integrations' },
      { number: 5, name: 'Preferences' },
      { number: 6, name: 'Templates' },
      { number: 7, name: 'Workflows' },
      { number: 8, name: 'Training' },
      { number: 9, name: 'Review' },
      { number: 10, name: 'Launch' }
    ]
  };

  const steps = stepConfigs[totalSteps] || stepConfigs[5];

  return (
    <div className="progress-indicator">
      <div className="progress-header">
        <span className="progress-text">
          Step {currentStep} of {totalSteps}
        </span>
        <span className="progress-percentage">
          {Math.round(progressPercentage)}% Complete
        </span>
      </div>

      <div className="progress-bar-container">
        <div
          className="progress-bar-fill"
          style={{ width: `${progressPercentage}%` }}
        ></div>
      </div>

      <div className="progress-steps">
        {steps.map((step) => (
          <div
            key={step.number}
            className={`progress-step ${
              step.number < currentStep ? 'completed' : ''
            } ${step.number === currentStep ? 'active' : ''}`}
          >
            <div className="step-circle">
              {step.number < currentStep ? (
                <svg
                  className="checkmark"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="3"
                >
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              ) : (
                <span className="step-number">{step.number}</span>
              )}
            </div>
            <span className="step-name">{step.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ProgressIndicator;
