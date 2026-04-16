import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import ProgressIndicator from './ProgressIndicator';
import Step1Registration from './steps/Step1Registration';
import Step2ProfileSetup from './steps/Step2ProfileSetup';
import Step3AIPreferences from './steps/Step3AIPreferences';
import Step4Training from './steps/Step4Training';
import Step5Confirmation from './steps/Step5Confirmation';
import './OnboardingWizard.css';
import { toast } from '../../utils/toast';
import { getToken } from '../../utils/tokenStore';

const TOTAL_STEPS = 5;
const API_BASE = 'https://api.perenniaai.com/api';
const API_V1 = `${API_BASE}/v1`;

const OnboardingWizard = () => {
  const { step } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const currentStep = parseInt(step) || 1;

  // Get invite token from URL if present
  const inviteToken = searchParams.get('token');

  const [progressId, setProgressId] = useState(null);
  const [inviteData, setInviteData] = useState(null);
  const [allStepData, setAllStepData] = useState({
    step1: {},
    step2: {},
    step3: {},
    step4: {},
    step5: {}
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [autoSaveStatus, setAutoSaveStatus] = useState('');
  const [error, setError] = useState(null);

  // Load progress on mount
  useEffect(() => {
    initializeOnboarding();
  }, []);

  // Auto-save every 30 seconds
  useEffect(() => {
    if (!progressId) return;

    const autoSaveInterval = setInterval(() => {
      autoSave();
    }, 30000);

    return () => clearInterval(autoSaveInterval);
  }, [progressId, allStepData, currentStep]);

  const initializeOnboarding = async () => {
    try {
      // If there's an invite token, validate it first
      if (inviteToken) {
        await validateInviteToken(inviteToken);
      }

      await loadProgress();
    } catch (error) {
      console.error('Error initializing onboarding:', error);
      setError('Failed to initialize onboarding. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const validateInviteToken = async (token) => {
    try {
      // Use the public invite endpoint
      const response = await fetch(`${API_BASE}/invite/${token}`);

      if (response.ok) {
        const data = await response.json();
        setInviteData(data);

        // Pre-populate step 2 with invite data
        setAllStepData(prev => ({
          ...prev,
          step2: {
            ...prev.step2,
            first_name: data.first_name || '',
            last_name: data.last_name || ''
          }
        }));
      } else if (response.status === 404 || response.status === 400) {
        const errorData = await response.json().catch(() => ({}));
        setError(errorData.detail || 'This invite link is invalid or has expired.');
      }
    } catch (error) {
      console.error('Error validating invite:', error);
    }
  };

  const loadProgress = async () => {
    try {
      const token = getToken();
      const response = await fetch(`${API_V1}/onboarding/resume`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setProgressId(data.id);

        // Load all step data
        const loadedData = {
          step1: data.step_1_data || {},
          step2: data.step_2_data || {},
          step3: data.step_3_data || {},
          step4: data.step_4_data || {},
          step5: data.step_5_data || {}
        };
        setAllStepData(prev => ({
          ...prev,
          ...loadedData
        }));

        // If current URL step doesn't match saved progress, redirect
        if (data.current_step && data.current_step !== currentStep) {
          navigate(`/onboarding/${data.current_step}${inviteToken ? `?token=${inviteToken}` : ''}`);
        }
      } else if (response.status === 404) {
        // No progress found, start new onboarding
        await startOnboarding();
      }
    } catch (error) {
      console.error('Error loading progress:', error);
    }
  };

  const startOnboarding = async () => {
    try {
      const token = getToken();
      const response = await fetch(`${API_V1}/onboarding/start`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          invite_token: inviteToken || null
        })
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
    if (!progressId) return;

    const currentStepData = allStepData[`step${currentStep}`];
    if (!currentStepData || Object.keys(currentStepData).length === 0) return;

    try {
      setAutoSaveStatus('Saving...');
      const token = getToken();

      const response = await fetch(`${API_V1}/onboarding/auto-save`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          step_number: currentStep,
          step_data: currentStepData
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
      const token = getToken();

      const response = await fetch(`${API_V1}/onboarding/step-${currentStep}/save`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });

      if (response.ok) {
        setAllStepData(prev => ({
          ...prev,
          [`step${currentStep}`]: data
        }));
        return true;
      } else {
        const errorData = await response.json();
        console.error('Save error:', errorData);
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
      const token = getToken();

      const response = await fetch(`${API_V1}/onboarding/step/${currentStep}/complete`, {
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
    const currentStepData = allStepData[`step${currentStep}`];

    // Save current step data
    const saved = await saveStep(currentStepData);
    if (!saved) {
      toast.error('Please fix the errors before proceeding.');
      return;
    }

    // Mark step as complete
    const completed = await completeStep();
    if (!completed) {
      toast.error('Error completing step. Please try again.');
      return;
    }

    // Navigate to next step
    if (currentStep < TOTAL_STEPS) {
      navigate(`/onboarding/${currentStep + 1}${inviteToken ? `?token=${inviteToken}` : ''}`);
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      navigate(`/onboarding/${currentStep - 1}${inviteToken ? `?token=${inviteToken}` : ''}`);
    }
  };

  const handleSaveAndExit = async () => {
    const currentStepData = allStepData[`step${currentStep}`];
    await saveStep(currentStepData);
    navigate('/dashboard');
  };

  const handleStepDataChange = (newData) => {
    setAllStepData(prev => ({
      ...prev,
      [`step${currentStep}`]: {
        ...prev[`step${currentStep}`],
        ...newData
      }
    }));
  };

  const handleOnboardingComplete = async () => {
    try {
      setIsSaving(true);
      const token = getToken();

      // Complete onboarding
      const response = await fetch(`${API_V1}/onboarding/complete`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          invite_token: inviteToken || null
        })
      });

      if (response.ok) {
        // Navigate to dashboard
        navigate('/dashboard?onboarding=complete');
      } else {
        toast.error('Error completing onboarding. Please try again.');
      }
    } catch (error) {
      console.error('Error completing onboarding:', error);
      toast.error('Error completing onboarding. Please try again.');
    } finally {
      setIsSaving(false);
    }
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

  if (error) {
    return (
      <div className="onboarding-wizard">
        <div className="error-container">
          <div className="error-icon">⚠️</div>
          <h2>Oops!</h2>
          <p>{error}</p>
          <button
            className="btn-primary"
            onClick={() => navigate('/login')}
          >
            Return to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="onboarding-wizard">
      <div className="wizard-header">
        <h1>Welcome to Perennia AI</h1>
        <p className="wizard-subtitle">
          {inviteData
            ? `Hi ${inviteData.first_name}! Let's get you set up in just ${TOTAL_STEPS} simple steps`
            : `Let's get you set up in just ${TOTAL_STEPS} simple steps`
          }
        </p>
      </div>

      <ProgressIndicator currentStep={currentStep} totalSteps={TOTAL_STEPS} />

      {autoSaveStatus && (
        <div className={`auto-save-indicator ${autoSaveStatus === 'Save failed' ? 'error' : ''}`}>
          {autoSaveStatus}
        </div>
      )}

      <div className="wizard-content">
        {currentStep === 1 && (
          <Step1Registration
            data={allStepData.step1}
            onChange={handleStepDataChange}
          />
        )}
        {currentStep === 2 && (
          <Step2ProfileSetup
            data={allStepData.step2}
            onChange={handleStepDataChange}
            inviteData={inviteData}
          />
        )}
        {currentStep === 3 && (
          <Step3AIPreferences
            data={allStepData.step3}
            onChange={handleStepDataChange}
          />
        )}
        {currentStep === 4 && (
          <Step4Training
            data={allStepData.step4}
            onChange={handleStepDataChange}
          />
        )}
        {currentStep === 5 && (
          <Step5Confirmation
            profileData={allStepData.step2}
            aiPreferences={allStepData.step3}
            trainingData={allStepData.step4}
            onComplete={handleOnboardingComplete}
          />
        )}
      </div>

      {currentStep < 5 && (
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
              {isSaving ? 'Saving...' : 'Next →'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default OnboardingWizard;
