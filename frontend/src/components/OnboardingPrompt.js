import React from 'react';
import { useNavigate } from 'react-router-dom';
import './OnboardingPrompt.css';

const OnboardingPrompt = () => {
  const navigate = useNavigate();

  const handleStartOnboarding = () => {
    navigate('/onboarding');
  };

  return (
    <div className="onboarding-prompt persistent">
      <div className="onboarding-prompt-content">
        <div className="onboarding-prompt-icon">🚀</div>
        <div className="onboarding-prompt-text">
          <h3>Complete Your Account Setup</h3>
          <p>
            You need to complete the onboarding wizard to access all features.
            We'll help you configure your team, processes, integrations, and AI assistant in just a few minutes.
          </p>
        </div>
        <div className="onboarding-prompt-actions">
          <button className="btn-start-onboarding" onClick={handleStartOnboarding}>
            Complete Setup Now
          </button>
        </div>
        <div className="onboarding-requirement-note">
          This prompt will remain until onboarding is completed.
        </div>
      </div>
    </div>
  );
};

export default OnboardingPrompt;
