import React, { useState, useEffect } from 'react';
import './OnboardingWizard.css';

const OnboardingWizard = ({ onComplete }) => {
  const [currentStep, setCurrentStep] = useState(1);
  const [steps, setSteps] = useState([]);
  const [stepsCompleted, setStepsCompleted] = useState([]);
  const [loading, setLoading] = useState(true);
  const [formData, setFormData] = useState({});

  useEffect(() => {
    fetchOnboardingData();
  }, []);

  const fetchOnboardingData = async () => {
    try {
      const token = localStorage.getItem('token');

      // Fetch steps and progress in parallel
      const [stepsRes, progressRes] = await Promise.all([
        fetch('/api/v1/onboarding/steps', {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch('/api/v1/onboarding/progress', {
          headers: { 'Authorization': `Bearer ${token}` }
        })
      ]);

      const stepsData = await stepsRes.json();
      const progressData = await progressRes.json();

      setSteps(stepsData.steps || []);
      setCurrentStep(progressData.current_step || 1);
      setStepsCompleted(progressData.steps_completed || []);
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch onboarding data:', error);
      setLoading(false);
    }
  };

  const handleNext = async () => {
    // Mark current step as completed
    const updatedCompleted = [...stepsCompleted];
    if (!updatedCompleted.includes(currentStep)) {
      updatedCompleted.push(currentStep);
    }

    setStepsCompleted(updatedCompleted);

    // Update progress on backend
    try {
      const token = localStorage.getItem('token');
      await fetch('/api/v1/onboarding/progress', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          current_step: currentStep + 1,
          steps_completed: updatedCompleted
        })
      });
    } catch (error) {
      console.error('Failed to update progress:', error);
    }

    // Move to next step or complete
    if (currentStep < steps.length) {
      setCurrentStep(currentStep + 1);
    } else {
      handleComplete();
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSkip = () => {
    handleNext();
  };

  const handleComplete = async () => {
    try {
      const token = localStorage.getItem('token');
      await fetch('/api/v1/onboarding/complete', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (onComplete) {
        onComplete();
      }
    } catch (error) {
      console.error('Failed to complete onboarding:', error);
    }
  };

  const handleFieldChange = (fieldName, value) => {
    setFormData({
      ...formData,
      [fieldName]: value
    });
  };

  const renderField = (field) => {
    switch (field.type) {
      case 'file':
        return (
          <div className="onboarding-field" key={field.name}>
            <label>{field.label}</label>
            <input
              type="file"
              multiple={field.multiple}
              onChange={(e) => handleFieldChange(field.name, e.target.files)}
              className="file-input"
            />
          </div>
        );

      case 'email':
        return (
          <div className="onboarding-field" key={field.name}>
            <label>{field.label}</label>
            <input
              type="email"
              value={formData[field.name] || ''}
              onChange={(e) => handleFieldChange(field.name, e.target.value)}
              className="text-input"
              placeholder={field.label}
            />
          </div>
        );

      case 'select':
        return (
          <div className="onboarding-field" key={field.name}>
            <label>{field.label}</label>
            <select
              value={formData[field.name] || ''}
              onChange={(e) => handleFieldChange(field.name, e.target.value)}
              className="select-input"
            >
              <option value="">Select {field.label}</option>
              {field.options && field.options.map(option => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>
        );

      case 'button':
        return (
          <div className="onboarding-field" key={field.name}>
            <button className="action-button" onClick={() => handleFieldAction(field.action)}>
              {field.label}
            </button>
          </div>
        );

      default:
        return null;
    }
  };

  const handleFieldAction = (action) => {
    // Handle button actions like OAuth redirects
    if (action === 'email_oauth') {
      // Redirect to email OAuth
      window.location.href = '/api/v1/email/oauth/authorize';
    } else if (action === 'calendar_oauth') {
      // Implement calendar OAuth
      console.log('Calendar OAuth not yet implemented');
    }
  };

  if (loading) {
    return (
      <div className="onboarding-overlay">
        <div className="onboarding-wizard">
          <div className="loading-spinner">Loading onboarding...</div>
        </div>
      </div>
    );
  }

  const currentStepData = steps.find(s => s.step_number === currentStep) || steps[0];
  const isLastStep = currentStep === steps.length;
  const progress = (currentStep / steps.length) * 100;

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-wizard">
        {/* Progress Bar */}
        <div className="progress-container">
          <div className="progress-bar" style={{ width: `${progress}%` }}></div>
        </div>

        {/* Step Indicator */}
        <div className="step-indicator">
          {steps.map((step, index) => (
            <div
              key={index}
              className={`step-dot ${step.step_number <= currentStep ? 'active' : ''} ${
                stepsCompleted.includes(step.step_number) ? 'completed' : ''
              }`}
            >
              {stepsCompleted.includes(step.step_number) ? '✓' : step.step_number}
            </div>
          ))}
        </div>

        {/* Step Content */}
        <div className="step-content">
          <div className="step-icon">{currentStepData.icon}</div>
          <h2>{currentStepData.title}</h2>
          <p className="step-description">{currentStepData.description}</p>

          {/* Render form fields */}
          {currentStepData.fields && currentStepData.fields.length > 0 && (
            <div className="step-fields">
              {currentStepData.fields.map(field => renderField(field))}
            </div>
          )}
        </div>

        {/* Navigation Buttons */}
        <div className="wizard-actions">
          {currentStep > 1 && (
            <button className="btn-back" onClick={handleBack}>
              ← Back
            </button>
          )}

          <div className="right-actions">
            {!currentStepData.required && !isLastStep && (
              <button className="btn-skip" onClick={handleSkip}>
                Skip
              </button>
            )}

            <button className="btn-next" onClick={handleNext}>
              {isLastStep ? 'Get Started! 🚀' : 'Next →'}
            </button>
          </div>
        </div>

        {/* Step Counter */}
        <div className="step-counter">
          Step {currentStep} of {steps.length}
        </div>
      </div>
    </div>
  );
};

export default OnboardingWizard;
