import React from 'react';
import { useNavigate } from 'react-router-dom';
import OnboardingWizard from '../components/OnboardingWizard';
import './Onboarding.css';

const Onboarding = () => {
  const navigate = useNavigate();

  const handleOnboardingComplete = () => {
    // Update localStorage to mark onboarding as completed
    try {
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const user = JSON.parse(userStr);
        user.onboarding_completed = true;
        localStorage.setItem('user', JSON.stringify(user));
      }
    } catch (error) {
      console.error('Error updating user data:', error);
    }

    // Navigate to dashboard
    navigate('/dashboard');
  };

  const handleOnboardingSkip = () => {
    // Mark as completed when skipped
    try {
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const user = JSON.parse(userStr);
        user.onboarding_completed = true;
        localStorage.setItem('user', JSON.stringify(user));
      }
    } catch (error) {
      console.error('Error updating user data:', error);
    }

    // Navigate to dashboard
    navigate('/dashboard');
  };

  return (
    <div className="onboarding-page">
      <OnboardingWizard
        onComplete={handleOnboardingComplete}
        onSkip={handleOnboardingSkip}
      />
    </div>
  );
};

export default Onboarding;
