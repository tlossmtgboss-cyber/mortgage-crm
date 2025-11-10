import React from 'react';
import { useNavigate } from 'react-router-dom';
import './OnboardingPrompt.css';

const OnboardingPrompt = ({ onDismiss }) => {
  const navigate = useNavigate();

  const handleStartOnboarding = () => {
    navigate('/onboarding');
  };

  return (
    <div className="onboarding-prompt">
      <div className="onboarding-prompt-content">
        <div className="onboarding-prompt-icon">🚀</div>
        <div className="onboarding-prompt-text">
          <h3>Welcome to your Mortgage CRM!</h3>
          <p>
            Let's get you set up with our onboarding wizard. We'll help you configure your team,
            processes, integrations, and AI assistant in just a few minutes.
          </p>
        </div>
        <div className="onboarding-prompt-actions">
          <button className="btn-start-onboarding" onClick={handleStartOnboarding}>
            Start Setup
          </button>
          <button className="btn-dismiss" onClick={onDismiss}>
            Remind Me Later
          </button>
        </div>
      </div>
    </div>
  );
};

export default OnboardingPrompt;
