import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ProgressIndicator from './ProgressIndicator';
import Step1Registration from './steps/Step1Registration';
import './OnboardingWizard.css';

const OnboardingWizard = () => {
  const { step } = useParams();
  const navigate = useNavigate();
  const currentStep = parseInt(step) || 1;

  const [progressId, setProgressId] = useState(null);
  const [stepData, setStepData] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [autoSaveStatus, setAutoSaveStatus] = useState('');

  // Load progress on mount
  useEffect(() => {
    loadProgress();
  }, []);

  // Auto-save every 30 seconds
  useEffect(() => {
    if (!progressId) return;

    const autoSaveInterval = setInterval(() => {
      autoSave();
    }, 30000); // 30 seconds

    return () => clearInterval(autoSaveInterval);
  }, [progressId, stepData, currentStep]);

  const loadProgress = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('https://mortgage-crm-production-7a9a.up.railway.app/api/v1/onboarding/resume', {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setProgressId(data.id);

        // Load step-specific data if it exists
        const stepKey = `step_${currentStep}_data`;
        if (data[stepKey]) {
          setStepData(data[stepKey]);
        }

        // If current URL step doesn't match saved progress, redirect
        if (data.current_step !== currentStep) {
          navigate(`/onboarding/${data.current_step}`);
        }
      } else if (response.status === 404) {
        // No progress found, start new onboarding
        await startOnboarding();
      }
    } catch (error) {
      console.error('Error loading progress:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const startOnboarding = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('https://mortgage-crm-production-7a9a.up.railway.app/api/v1/onboarding/start', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setProgressId(data.progress_id);
      }
    } catch (error) {
      console.error('Error starting onboarding:', error);
    }
  };

  const autoSave = async () => {
    if (!progressId || Object.keys(stepData).length === 0) return;

    try {
      setAutoSaveStatus('Saving...');
      const token = localStorage.getItem('token');

      const response = await fetch('https://mortgage-crm-production-7a9a.up.railway.app/api/v1/onboarding/auto-save', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          step_number: currentStep,
          step_data: stepData
        })
      });

      if (response.ok) {
        setAutoSaveStatus('Saved');
        setTimeout(() => setAutoSaveStatus(''), 2000);
      }
    } catch (error) {
      console.error('Auto-save error:', error);
      setAutoSaveStatus('Save failed');
      setTimeout(() => setAutoSaveStatus(''), 3000);
    }
  };

  const saveStep = async (data) => {
    try {
      setIsSaving(true);
      const token = localStorage.getItem('token');

      const response = await fetch(`https://mortgage-crm-production-7a9a.up.railway.app/api/v1/onboarding/step-${currentStep}/save`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });

      if (response.ok) {
        setStepData(data);
        return true;
      } else {
        const error = await response.json();
        console.error('Save error:', error);
        return false;
      }
    } catch (error) {
      console.error('Save error:', error);
      return false;
    } finally {
      setIsSaving(false);
    }
  };

  const completeStep = async () => {
    try {
      const token = localStorage.getItem('token');

      const response = await fetch(`https://mortgage-crm-production-7a9a.up.railway.app/api/v1/onboarding/step/${currentStep}/complete`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      return response.ok;
    } catch (error) {
      console.error('Complete step error:', error);
      return false;
    }
  };

  const handleNext = async () => {
    // Save current step data
    const saved = await saveStep(stepData);
    if (!saved) {
      alert('Please fix the errors before proceeding.');
      return;
    }

    // Mark step as complete
    const completed = await completeStep();
    if (!completed) {
      alert('Error completing step. Please try again.');
      return;
    }

    // Navigate to next step
    if (currentStep < 10) {
      navigate(`/onboarding/${currentStep + 1}`);
    } else {
      // Onboarding complete
      navigate('/dashboard');
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      navigate(`/onboarding/${currentStep - 1}`);
    }
  };

  const handleSaveAndExit = async () => {
    await saveStep(stepData);
    navigate('/dashboard');
  };

  const handleStepDataChange = (newData) => {
    setStepData(prevData => ({
      ...prevData,
      ...newData
    }));
  };

  if (isLoading) {
    return (
      <div className="onboarding-wizard">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Loading your progress...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="onboarding-wizard">
      <div className="wizard-header">
        <h1>Welcome to Your CRM Setup</h1>
        <p className="wizard-subtitle">Let's get you set up in just 10 simple steps</p>
      </div>

      <ProgressIndicator currentStep={currentStep} totalSteps={10} />

      {autoSaveStatus && (
        <div className={`auto-save-indicator ${autoSaveStatus === 'Save failed' ? 'error' : ''}`}>
          {autoSaveStatus}
        </div>
      )}

      <div className="wizard-content">
        {currentStep === 1 && (
          <Step1Registration
            data={stepData}
            onChange={handleStepDataChange}
          />
        )}
        {currentStep === 2 && (
          <div className="placeholder-step">
            <h2>Step 2: Coming Soon</h2>
            <p>This step will be implemented in the next phase.</p>
          </div>
        )}
        {currentStep >= 3 && currentStep <= 10 && (
          <div className="placeholder-step">
            <h2>Step {currentStep}: Coming Soon</h2>
            <p>This step will be implemented in future phases.</p>
          </div>
        )}
      </div>

      <div className="wizard-footer">
        <div className="footer-left">
          <button
            type="button"
            className="btn-secondary"
            onClick={handleSaveAndExit}
            disabled={isSaving}
          >
            Save & Exit
          </button>
        </div>
        <div className="footer-right">
          {currentStep > 1 && (
            <button
              type="button"
              className="btn-secondary"
              onClick={handleBack}
              disabled={isSaving}
            >
              ← Back
            </button>
          )}
          <button
            type="button"
            className="btn-primary"
            onClick={handleNext}
            disabled={isSaving}
          >
            {currentStep === 10 ? 'Complete Setup' : 'Next →'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default OnboardingWizard;
